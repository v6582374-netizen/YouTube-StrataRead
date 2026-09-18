import { expect } from "@playwright/test";
import { test } from "./fixtures";

for (const width of [800, 1100, 1440]) {
  test(`YouTube shared views and persistent settings at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 850 });
    if (width === 1100)
      await page.addInitScript(() =>
        localStorage.setItem("openwork-theme", "dark"),
      );
    let exclusions: string[] = [];
    let prompt = "将字幕整理为忠实的简体中文文档。";
    let opened = 0;
    let sourceOpened = 0;
    await page.route("**/v1/youtube/capability", async (route) => {
      const { capability, arguments: args = {} } = route
        .request()
        .postDataJSON();
      const asset = {
        video_id: "one",
        title: "一份用于验证整合的稿件",
        channel_title: "Example channel",
        channel_id: "channel",
        published_at: new Date().toISOString(),
        preparation_state: "ready",
        reading_state: "inbox",
        manuscript_version: 1,
        excerpt: "忠实保留原文的信息与论证。",
        manuscript_characters: 3000,
      };
      let result: unknown = {};
      if (capability === "library.list") {
        expect(args.documents_only).toBe(true);
        result = { assets: [asset], total: 1 };
      }
      if (capability === "collection.set_exclusions")
        exclusions = args.excluded_channels;
      if (
        capability === "collection.preferences" ||
        capability === "collection.set_exclusions"
      )
        result = {
          sources: [{ channel_id: "channel", title: "Example channel" }],
          excluded_channels: exclusions,
        };
      if (capability === "generation.set_prompt") prompt = args.prompt;
      if (
        capability === "generation.prompt" ||
        capability === "generation.set_prompt"
      )
        result = { prompt, default_prompt: "默认忠实整理规则" };
      if (capability === "activity.snapshot")
        result = {
          queued: 0,
          acquiring: 0,
          generating: 0,
          ready: 1,
          failed: 0,
          unavailable: 0,
          drain_paused: false,
          batch: { completed: 1, limit: 100 },
          model: "not-visible-model",
          model_ready: true,
          failures: [],
        };
      if (capability === "library.inspect")
        result = {
          ...asset,
          source_trace: {
            video_url: "https://www.youtube.com/watch?v=one",
            transcript_available: true,
          },
          generation_records: [],
        };
      if (capability === "sources.open") {
        sourceOpened++;
        result = { opened: true };
      }
      if (capability === "documents.open") {
        opened++;
        result = { opened: true };
      }
      await route.fulfill({ json: { ok: true, result } });
    });
    await page.goto("/");
    await page.getByTestId("nav-youtube").click();
    const main = page.getByRole("main", { name: "YouTube 资料库" });
    await expect(
      main.getByRole("heading", { name: "YouTube", exact: true }),
    ).toBeVisible();
    await expect(main.getByText("not-visible-model")).toHaveCount(0);
    await expect(main.getByRole("button", { name: "收件箱" })).toHaveCount(0);
    await main
      .getByRole("combobox", { name: "按时间筛选" })
      .selectOption("all");
    for (const layout of ["时间流", "文档库", "频道索引"]) {
      await main.getByRole("button", { name: layout, exact: true }).click();
      await expect(
        main.getByRole("combobox", { name: "按时间筛选" }),
      ).toHaveValue("all");
      await expect(
        main.getByRole("button", { name: /一份用于验证整合的稿件/ }),
      ).toBeVisible();
      expect(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      ).toBe(true);
      await page.screenshot({
        path: `test-results/youtube-${width}-${layout}.png`,
      });
    }
    await main.getByRole("button", { name: /一份用于验证整合的稿件/ }).click();
    const dialog = page.getByRole("dialog", { name: "文档信息" });
    await expect(dialog).toBeVisible();
    expect(opened).toBe(0);
    expect(sourceOpened).toBe(0);
    await dialog.getByRole("button", { name: "打开 YouTube" }).click();
    await expect.poll(() => sourceOpened).toBe(1);
    await dialog.getByRole("button", { name: "用默认应用打开" }).click();
    await expect.poll(() => opened).toBe(1);
    await page.keyboard.press("Escape");
    await main.getByRole("button", { name: "订阅频道", exact: true }).click();
    await page
      .getByRole("checkbox", { name: "自动生成 Example channel" })
      .uncheck();
    await page.getByRole("button", { name: "保存", exact: true }).click();
    await expect.poll(() => exclusions).toEqual(["channel"]);
    await expect(page.getByRole("dialog")).toHaveCount(0);
    await main.getByRole("button", { name: "生成规则" }).click();
    await page
      .getByLabel("Prompt", { exact: true })
      .fill("保留原文观点，不添加事实。");
    await page.getByRole("button", { name: "保存规则" }).click();
    await expect.poll(() => prompt).toBe("保留原文观点，不添加事实。");
    await page.reload();
    await page.getByTestId("nav-youtube").click();
    await expect(
      main.getByRole("button", { name: "频道索引" }),
    ).toHaveAttribute("aria-pressed", "true");
    await main.getByRole("button", { name: "生成规则" }).click();
    await expect(page.getByLabel("Prompt", { exact: true })).toHaveValue(
      prompt,
    );
  });
}
