import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { YouTubeView } from "./YouTubeView";
import { youtubeCapability } from "../api";
vi.mock("../api", () => ({ youtubeCapability: vi.fn() }));
const call = vi.mocked(youtubeCapability);
const asset = {
  video_id: "one",
  channel_id: "channel",
  channel_title: "Example",
  title: "Prepared manuscript",
  url: "https://www.youtube.com/watch?v=one",
  published_at: new Date().toISOString(),
  preparation_state: "ready",
  reading_state: "inbox",
  manuscript_version: 1,
  excerpt: "Useful source text",
  manuscript_characters: 1500,
};
const activity = {
  queued: 1,
  acquiring: 0,
  generating: 0,
  ready: 1,
  failed: 0,
  unavailable: 0,
  drain_paused: false,
  batch: { completed: 1, limit: 100 },
  model: "host/model",
  model_ready: false,
  failures: [],
};
beforeEach(() => {
  call.mockReset();
  call.mockImplementation(async (capability) => {
    if (capability === "library.list") return { assets: [asset] };
    if (capability === "activity.snapshot") return activity;
    if (capability === "collection.preferences")
      return {
        sources: [{ channel_id: "channel", title: "Example" }],
        excluded_channels: [],
      };
    if (capability === "generation.prompt")
      return {
        prompt: "Original instruction",
        default_prompt: "Default instruction",
      };
    if (capability === "collection.set_exclusions")
      return {
        sources: [{ channel_id: "channel", title: "Example" }],
        excluded_channels: ["channel"],
      };
    if (capability === "library.inspect")
      return {
        ...asset,
        source_trace: { video_url: asset.url, transcript_available: true },
        generation_records: [],
      };
    if (capability === "connection.status") return new Promise(() => {});
    return {};
  });
});
afterEach(cleanup);
describe("YouTube document views", () => {
  it("keeps host configuration out of the normal UI and opens connection immediately", async () => {
    render(<YouTubeView onModelSettings={() => {}} />);
    await screen.findByRole("button", { name: /Prepared manuscript/ });
    expect(screen.queryByText(/host\/model/)).toBeNull();
    expect(screen.queryByRole("button", { name: "收件箱" })).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "订阅频道" }));
    fireEvent.click(
      await screen.findByRole("button", { name: "连接 YouTube" }),
    );
    expect(screen.getByRole("dialog", { name: "连接 YouTube" })).toBeTruthy();
  });
  it("offers three presentations without clearing the shared filters and remembers the choice", async () => {
    const component = render(<YouTubeView onModelSettings={() => {}} />);
    await screen.findByRole("button", { name: /Prepared manuscript/ });
    fireEvent.change(screen.getByRole("combobox", { name: "按时间筛选" }), {
      target: { value: "all" },
    });
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索文档" }), {
      target: { value: "science" },
    });
    for (const name of ["文档库", "频道索引", "时间流"]) {
      fireEvent.click(screen.getByRole("button", { name }));
      expect(
        (
          screen.getByRole("searchbox", {
            name: "搜索文档",
          }) as HTMLInputElement
        ).value,
      ).toBe("science");
      expect(
        (
          screen.getByRole("combobox", {
            name: "按时间筛选",
          }) as HTMLSelectElement
        ).value,
      ).toBe("all");
    }
    fireEvent.click(screen.getByRole("button", { name: "文档库" }));
    component.unmount();
    render(<YouTubeView onModelSettings={() => {}} />);
    expect(
      screen
        .getByRole("button", { name: "文档库" })
        .getAttribute("aria-pressed"),
    ).toBe("true");
  });
  it("saves exclusions and Prompt through real capabilities only on explicit save", async () => {
    render(<YouTubeView onModelSettings={() => {}} />);
    await screen.findByRole("button", { name: /Prepared manuscript/ });
    fireEvent.click(screen.getByRole("button", { name: "订阅频道" }));
    fireEvent.click(
      await screen.findByRole("checkbox", { name: "自动生成 Example" }),
    );
    expect(
      call.mock.calls.some(([c]) => c === "collection.set_exclusions"),
    ).toBe(false);
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith("collection.set_exclusions", {
        excluded_channels: ["channel"],
      }),
    );
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    fireEvent.click(screen.getByRole("button", { name: "生成规则" }));
    const input = await screen.findByLabelText("Prompt");
    await waitFor(() =>
      expect((input as HTMLTextAreaElement).value).toBe("Original instruction"),
    );
    fireEvent.change(input, { target: { value: "New faithful instructions" } });
    fireEvent.click(screen.getByRole("button", { name: "保存规则" }));
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith("generation.set_prompt", {
        prompt: "New faithful instructions",
      }),
    );
  });
  it("shows provenance without automatically opening a document", async () => {
    render(<YouTubeView onModelSettings={() => {}} />);
    fireEvent.click(
      await screen.findByRole("button", { name: /Prepared manuscript/ }),
    );
    const dialog = await screen.findByRole("dialog", { name: "文档信息" });
    const open = await within(dialog).findByRole("button", {
      name: "用默认应用打开",
    });
    expect(call.mock.calls.some(([c]) => c === "documents.open")).toBe(false);
    fireEvent.click(open);
    await waitFor(() =>
      expect(call).toHaveBeenCalledWith("documents.open", { video_id: "one" }),
    );
  });
});

it("never exposes the previous document after the next inspection fails", async () => {
  const implementation = call.getMockImplementation()!;
  call.mockImplementation(async (capability, args) => {
    if (capability === "library.list")
      return {
        assets: [
          asset,
          { ...asset, video_id: "two", title: "Unavailable document" },
        ],
      };
    if (capability === "library.inspect" && args?.video_id === "two")
      throw new Error("文档不可用");
    return implementation(capability, args);
  });
  render(<YouTubeView onModelSettings={() => {}} />);
  fireEvent.click(
    await screen.findByRole("button", { name: /Prepared manuscript/ }),
  );
  await screen.findByRole("button", { name: "删除文档" });
  fireEvent.click(screen.getByRole("button", { name: "关闭" }));
  fireEvent.click(screen.getByRole("button", { name: /Unavailable document/ }));
  await screen.findByText("文档不可用");
  expect(
    within(screen.getByRole("dialog")).queryByRole("button", {
      name: "删除文档",
    }),
  ).toBeNull();
});

it("does not save stale rules after a failed Prompt load", async () => {
  render(<YouTubeView onModelSettings={() => {}} />);
  fireEvent.click(screen.getByRole("button", { name: "生成规则" }));
  await waitFor(() =>
    expect((screen.getByLabelText("Prompt") as HTMLTextAreaElement).value).toBe(
      "Original instruction",
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "取消" }));
  const implementation = call.getMockImplementation()!;
  call.mockImplementation(async (capability, args) => {
    if (capability === "generation.prompt") throw new Error("无法读取规则");
    return implementation(capability, args);
  });
  fireEvent.click(screen.getByRole("button", { name: "生成规则" }));
  await screen.findByText("无法读取规则");
  expect(
    (screen.getByRole("button", { name: "保存规则" }) as HTMLButtonElement)
      .disabled,
  ).toBe(true);
});
