import { test, expect } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await page.clock.setFixedTime(new Date("2026-09-20T04:00:00Z"));
  await page.addInitScript(() => localStorage.setItem("openworker.lang", "zh"));
  await page.goto("/");
});

test("navigates holidays and make-up weeks without duplicating courses", async ({ page }) => {
  await page.getByRole("button", { name: "Curriculum", exact: true }).click();
  const view = page.getByRole("main", { name: "Curriculum" });
  const jump = view.getByLabel("跳转日期");
  await jump.fill("2026-09-25");
  await expect(view.getByRole("region", { name: "2026-09-25" }).getByRole("button")).toHaveCount(0);
  await expect(view).toContainText("中秋节放假");
  await jump.fill("2026-10-01");
  await expect(view.getByRole("heading", { name: "第 3 周", exact: true })).toBeVisible();
  await expect(view.getByRole("region", { name: "2026-10-01" }).getByRole("button")).toHaveCount(0);
  await expect(view).toContainText("国庆节放假");
  await view.getByRole("button", { name: "下一周", exact: true }).click();
  await expect(view.getByRole("heading", { name: "第 4 周", exact: true })).toBeVisible();
  await expect(view.getByRole("region", { name: "2026-10-10" }).getByRole("button")).toHaveCount(3);
  await expect(view.getByRole("region", { name: "2026-10-09" }).getByRole("button")).toHaveCount(3);
  await expect(view.getByRole("region", { name: "2026-10-05" }).getByRole("button")).toHaveCount(0);
  await expect(view).toContainText("上单周周五课程");
  await view.getByRole("button", { name: "上一周", exact: true }).click();
  await expect(view.getByRole("heading", { name: "第 3 周", exact: true })).toBeVisible();
  await jump.fill("2026-10-30");
  await expect(view.getByRole("region", { name: "2026-10-30" }).getByRole("button")).toHaveCount(0);
  await expect(view).toContainText("校运会");
  await jump.fill("2026-11-09");
  await expect(view).toContainText("期中考试，不停课");
  await expect(view.getByRole("region", { name: "2026-11-09" }).getByRole("button")).toHaveCount(2);
  await view.getByRole("button", { name: "本周", exact: true }).click();
  await expect(jump).toHaveValue("2026-09-20");
});

test("opens this week's actual courses from the sidebar, including Sunday's make-up classes", async ({ page }) => {
  await page.getByRole("button", { name: "Curriculum", exact: true }).click();
  const view = page.getByRole("main", { name: "Curriculum" });
  await expect(view.getByRole("heading", { name: "第 1 周", exact: true })).toBeVisible();
  await expect(view.getByLabel("跳转日期")).toHaveValue("2026-09-20");
  const sunday = view.getByRole("region", { name: "2026-09-20" });
  await expect(sunday.getByRole("button")).toHaveCount(3);
  await expect(sunday).toContainText("09:50–11:25");
  await expect(sunday).toContainText("理5A-306");
  const tuesday = view.getByRole("region", { name: "2026-09-15" });
  await expect(tuesday.getByRole("button", { name: /单片机应用技术/ })).toHaveCount(2);
  await expect(tuesday.getByRole("button", { name: /C\+\+程序设计及上机/ })).toHaveCount(2);
  await expect(tuesday).toContainText("文3-115");
  await expect(tuesday).toContainText("理5A-302");
});

test("keeps the final Monday's courses and distinguishes missing spring data from an empty week", async ({ page }) => {
  await page.getByRole("button", { name: "Curriculum", exact: true }).click();
  const view = page.getByRole("main", { name: "Curriculum" });
  await view.getByLabel("跳转日期").fill("2027-01-11");
  await expect(view.getByRole("heading", { name: "第 18 周", exact: true })).toBeVisible();
  await expect(view.getByRole("region", { name: "2027-01-11" }).getByRole("button")).toHaveCount(3);
  await expect(view).toContainText("个人考试安排未提供");
  await view.getByLabel("跳转日期").fill("2027-01-18");
  await expect(view).toContainText("本周 0 次课程");
  await view.getByLabel("跳转日期").fill("2027-03-01");
  await expect(view.getByRole("heading", { name: "第 1 周", exact: true })).toBeVisible();
  await expect(view).toContainText("春季学期课表尚未提供");
  await expect(view).not.toContainText("无课程安排");
  await expect(view).not.toContainText("本周 0 次课程");
  await expect(view).toContainText("开始上课");
  await view.getByLabel("跳转日期").fill("2027-06-09");
  await expect(view).toContainText("端午节");
  await expect(view).toContainText("调休安排以学校通知为准");
  await view.getByLabel("跳转日期").fill("2027-07-05");
  await expect(view).toContainText("暑假（短学期）开始");
  await expect(view).toContainText("此时段未提供个人课表");
});

test("course details expose the correct teacher and class periods, then restore keyboard focus", async ({ page }) => {
  await page.getByRole("button", { name: "Curriculum", exact: true }).click();
  const view = page.getByRole("main", { name: "Curriculum" });
  const course = view.getByRole("region", { name: "2026-09-14" }).getByRole("button", { name: /物联网技术与原理/ });
  await course.click();
  const dialog = page.getByRole("dialog", { name: "物联网技术与原理" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("郑腾");
  await expect(dialog).toContainText("第 8–9 节");
  await expect(dialog).toContainText("15:20–16:55");
  await page.keyboard.press("Escape");
  await expect(dialog).not.toBeVisible();
  await expect(course).toBeFocused();
  await view.getByRole("region", { name: "2026-09-20" }).getByRole("button", { name: /物联网技术与原理/ }).click();
  await expect(page.getByRole("dialog")).toContainText("张懿");
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  await view.getByRole("region", { name: "2026-09-17" }).getByRole("button", { name: /可持续旅游与数字创新/ }).click();
  await expect(page.getByRole("dialog")).toContainText("全程外教英文授课");
});

test("weekly overview remains readable in both themes and a narrow window", async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await page.getByRole("button", { name: "Curriculum", exact: true }).click();
  await expect(page.locator(".curriculum-course")).toHaveCount(20);
  await page.screenshot({ path: testInfo.outputPath("curriculum-light.png") });
  await page.evaluate(() => document.documentElement.dataset.theme = "dark");
  await page.screenshot({ path: testInfo.outputPath("curriculum-dark.png") });
  await page.setViewportSize({ width: 900, height: 760 });
  const scroller = page.getByRole("region", { name: "每周课表" });
  await scroller.evaluate(element => element.scrollLeft = element.scrollWidth);
  await page.getByRole("region", { name: "2026-09-20" }).getByRole("button", { name: /物联网技术与原理/ }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath("curriculum-narrow.png") });
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByLabel("跳转日期").fill("2027-03-01");
  await expect(page.getByRole("status")).toBeInViewport();
});

test.describe("school timezone", () => {
  test.use({ timezoneId: "America/Los_Angeles" });

  test("uses Shanghai's Monday even when the computer is still on Sunday, with English controls", async ({ page }) => {
    await page.clock.setFixedTime(new Date("2026-09-20T16:30:00Z"));
    await page.addInitScript(() => localStorage.setItem("openworker.lang", "en"));
    await page.reload();
    await page.getByRole("button", { name: "Curriculum", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Week 2", exact: true })).toBeVisible();
    await expect(page.getByLabel("Jump to date")).toHaveValue("2026-09-21");
    await expect(page.getByRole("button", { name: "Next week", exact: true })).toBeVisible();
    await page.getByLabel("Jump to date").fill("2027-01-01");
    await expect(page.getByRole("heading", { name: "Week 16", exact: true })).toBeVisible();
    await expect(page.getByRole("region", { name: "2027-01-01" }).getByRole("button")).toHaveCount(0);
    await expect(page.getByRole("main", { name: "Curriculum" })).toContainText("New Year’s Day");
    await page.getByRole("button", { name: "This week", exact: true }).click();
    await expect(page.getByLabel("Jump to date")).toHaveValue("2026-09-21");
  });
});
