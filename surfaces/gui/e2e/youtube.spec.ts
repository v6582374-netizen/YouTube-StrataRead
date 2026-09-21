import { expect } from "@playwright/test";
import { test } from "./fixtures";
test.beforeEach(async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("openworker.lang", "zh"));
});

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
    const defaults = {
      version: 2, country: "",
      prompts: Object.fromEntries(["initial", "review", "revision", "composition"].map((stage) => [stage, {
        system: `${stage} 默认指令`, user: "{source_text} {translation}",
      }])), max_calls: 240, max_tokens: 1500000,
    };
    let config = structuredClone(defaults);
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
          sources: [
            { channel_id: "channel", title: "Example channel" },
            { channel_id: "other", title: "Another channel" },
            { channel_id: "third", title: "Third channel" },
          ],
          excluded_channels: exclusions,
        };
      if (capability === "translation.set_settings") config = args.settings;
      if (capability === "translation.settings" || capability === "translation.set_settings")
        result = { settings: config, defaults, required: {
          initial: { user: ["source_text"] }, review: { user: ["source_text", "translation"] },
          revision: { user: ["source_text", "translation"] }, composition: { user: ["translation"] },
        } };
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
    ).toHaveCount(0);
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
    await main.getByRole("button", { name: "订阅频道", exact: true }).click();
    const channels = page.getByRole("dialog", { name: "订阅频道" });
    await channels.getByRole("textbox", { name: "搜索订阅频道" }).fill("Example");
    await channels.getByRole("button", { name: "全不选", exact: true }).click();
    await expect(channels.getByText("0 个频道已开启", { exact: true })).toBeVisible();
    expect(exclusions).toEqual(["channel"]); // Bulk changes remain a draft.
    await channels.getByRole("button", { name: "取消", exact: true }).click();
    await main.getByRole("button", { name: "订阅频道", exact: true }).click();
    await expect(channels.getByText("2 个频道已开启", { exact: true })).toBeVisible();
    await channels.getByRole("button", { name: "全选", exact: true }).click();
    await expect(channels.getByText("3 个频道已开启", { exact: true })).toBeVisible();
    await channels.getByRole("button", { name: "保存", exact: true }).click();
    await expect.poll(() => exclusions).toEqual([]);
    await main.getByRole("button", { name: "订阅频道", exact: true }).click();
    await channels.getByRole("textbox", { name: "搜索订阅频道" }).fill("Example");
    await channels.getByRole("button", { name: "全不选", exact: true }).click();
    await channels.getByRole("button", { name: "保存", exact: true }).click();
    await expect.poll(() => exclusions).toEqual(["channel", "other", "third"]);
    await main.getByRole("button", { name: "生成规则" }).click();
    const settings = page.getByRole("region", { name: "YouTube 生成规则", exact: true });
    await expect(settings).toBeVisible();
    for (const name of ["初译", "审校", "修订", "成稿整理"]) {
      await settings.getByRole("tab", { name, exact: true }).click();
      await expect(settings.getByLabel("系统提示词")).toBeVisible();
      await expect(settings.getByLabel("任务模板", { exact: true })).toBeVisible();
    }
    await settings.getByLabel("系统提示词").fill("保留原文观点，不添加事实。");
    await settings.getByLabel("最多模型调用次数").fill("120");
    await settings.getByRole("button", { name: "保存设置" }).click();
    await expect.poll(() => config.prompts.composition.system).toBe("保留原文观点，不添加事实。");
    await expect.poll(() => config.max_calls).toBe(120);
    await expect(settings.getByRole("button", { name: "保存设置" })).toBeDisabled();
    await expect(settings.getByRole("status")).toContainText("已保存");
    await page.screenshot({ path: `test-results/youtube-translation-${width}.png` });
    await page.reload();
    await page.getByTestId("nav-youtube").click();
    await expect(
      main.getByRole("button", { name: "频道索引" }),
    ).toHaveAttribute("aria-pressed", "true");
    await main.getByRole("button", { name: "生成规则" }).click();
    await settings.getByRole("tab", { name: "成稿整理", exact: true }).click();
    await expect(settings.getByLabel("系统提示词")).toHaveValue("保留原文观点，不添加事实。");
    await expect(settings.getByLabel("最多模型调用次数")).toHaveValue("120");
    await settings.getByRole("button", { name: "恢复本阶段默认提示词" }).click();
    await expect(settings.getByLabel("系统提示词")).toHaveValue("composition 默认指令");
    // Restoring a template is a draft edit until explicitly saved.
    expect(config.prompts.composition.system).toBe("保留原文观点，不添加事实。");

  });
}
