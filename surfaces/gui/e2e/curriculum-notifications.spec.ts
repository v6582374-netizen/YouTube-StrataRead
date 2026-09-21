import { test, expect } from "./fixtures";

test.beforeEach(async ({ page }) => {
  // UI/native command contract; the Rust tests and macOS smoke exercise the service.
  await page.addInitScript(() => {
    localStorage.setItem("openworker.lang", "zh");
    (window as any).__OCW_PLATFORM__ = "macos";
    (window as any).__TAURI__ = { core: { invoke: async (command: string, args?: { enabled: boolean }) => {
      const saved = localStorage.getItem("test:notification-enabled");
      if (command === "set_course_notifications_enabled") localStorage.setItem("test:notification-enabled", String(args?.enabled));
      if (command === "get_course_notification_status" || command === "set_course_notifications_enabled") return {
        enabled: command === "set_course_notifications_enabled" ? args?.enabled : saved !== "false",
        permission: localStorage.getItem("test:notification-permission") || "granted", error: null,
      };
      return null;
    } } };
  });
  await page.goto("/");
  await page.getByRole("button", { name: "Curriculum", exact: true }).click();
});

test("notification preference defaults on and preserves an explicit off choice", async ({ page }) => {
  const toggle = page.getByRole("switch", { name: "课程通知", exact: true });
  await expect(toggle).toBeChecked();
  await expect(page.getByText("逐节次提醒上课与下课", { exact: true })).toBeVisible();
  await toggle.click();
  await expect(toggle).not.toBeChecked();
  await page.reload();
  await page.getByRole("button", { name: "Curriculum", exact: true }).click();
  await expect(toggle).not.toBeChecked();
  await expect(page.getByText("课程提醒已关闭", { exact: true })).toBeVisible();
});

test("denied system permission is distinct from the enabled preference", async ({ page }) => {
  await page.evaluate(() => localStorage.setItem("test:notification-permission", "denied"));
  await page.reload();
  await page.getByRole("button", { name: "Curriculum", exact: true }).click();
  await expect(page.getByRole("switch", { name: "课程通知", exact: true })).toBeChecked();
  await expect(page.getByText("请在系统设置 → 通知 → Edison 中允许通知", { exact: true })).toBeVisible();
  await expect(page.getByText("逐节次提醒上课与下课", { exact: true })).toHaveCount(0);
});
