import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { YouTubeTranslationSettings } from "./YouTubeTranslationSettings";
import i18n from "i18next";
import zh from "../locales/zh.json";
import { youtubeCapability } from "../api";
vi.mock("../api", () => ({ youtubeCapability: vi.fn() }));
const call = vi.mocked(youtubeCapability);
const templates = { initial: ["system", "user", "multichunk_user"], review: ["system", "user", "user_region", "multichunk_user", "multichunk_user_region"], revision: ["system", "user", "multichunk_user"], composition: ["system", "user"] };
const cfg = {
  version: 2, country: "",
  prompts: Object.fromEntries(Object.entries(templates).map(([stage, roles]) => [stage, Object.fromEntries(roles.map(role => [role, `${stage} ${role} {source_text}`]))])),
  max_calls: 240, max_tokens: 1500000,
};
const response = { settings: cfg, defaults: cfg, required: Object.fromEntries(Object.entries(templates).map(([stage, roles]) => [stage, Object.fromEntries(roles.map(role => [role, ["source_text"]]))])) };
beforeEach(() => {
  i18n.addResourceBundle("zh", "translation", zh);
  void i18n.changeLanguage("zh");
  call.mockReset(); call.mockResolvedValue(structuredClone(response));
});
afterEach(cleanup);
it("never exposes a save action after configuration fails to load", async () => {
  call.mockRejectedValue(new Error("配置暂不可用"));
  render(<YouTubeTranslationSettings />);
  expect(await screen.findByText("配置暂不可用")).toBeTruthy();
  expect(screen.queryByRole("button", { name: "保存设置" })).toBeNull();
  expect(call.mock.calls.every(([capability]) => capability === "translation.settings")).toBe(true);
});
it("keeps a rejected draft available for correction without reporting saved", async () => {
  render(<YouTubeTranslationSettings />);
  const input = await screen.findByLabelText("任务模板");
  fireEvent.change(input, { target: { value: "missing placeholder" } });
  call.mockRejectedValueOnce(new Error("缺少占位符：{source_text}"));
  fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
  expect(await screen.findByText("缺少占位符：{source_text}")).toBeTruthy();
  expect((input as HTMLTextAreaElement).value).toBe("missing placeholder");
  expect(screen.getByText("有未保存的修改")).toBeTruthy();
  await waitFor(() => expect((screen.getByRole("button", { name: "保存设置" }) as HTMLButtonElement).disabled).toBe(false));
});

it("edits and saves every upstream variant and region without losing other templates", async () => {
  render(<YouTubeTranslationSettings />);
  await screen.findByLabelText("任务模板");
  const labels = ["初译", "审校", "修订", "成稿整理"];
  for (const [index, [stage, roles]] of Object.entries(templates).entries()) {
    fireEvent.click(screen.getByRole("tab", { name: labels[index] }));
    fireEvent.change(screen.getByLabelText("系统提示词"), { target: { value: `${stage} edited system` } });
    for (const role of roles.filter(role => role !== "system")) {
      if (stage !== "composition") fireEvent.change(screen.getByLabelText("任务模板类型"), { target: { value: role } });
      fireEvent.change(screen.getByLabelText("任务模板"), { target: { value: `${stage} edited ${role} {source_text}` } });
    }
  }
  fireEvent.change(screen.getByLabelText("译文地区"), { target: { value: "中国大陆" } });
  call.mockImplementationOnce(async (_capability, args) => ({ ...response, settings: (args as { settings: typeof cfg }).settings }));
  fireEvent.click(screen.getByRole("button", { name: "保存设置" }));
  expect(await screen.findByText("已保存，后续新任务使用这些设置。")).toBeTruthy();
  const saved = (call.mock.calls[call.mock.calls.length - 1][1] as { settings: typeof cfg }).settings;
  expect(saved.country).toBe("中国大陆");
  for (const [stage, roles] of Object.entries(templates)) for (const role of roles) {
    expect(saved.prompts[stage][role]).toContain(`${stage} edited`);
  }
});
