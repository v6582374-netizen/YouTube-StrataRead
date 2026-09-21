import i18n from "i18next";

export function yt(value: string, values: Record<string, string | number | undefined> = {}): string {
  const source = value === "YouTube update feed could not be read"
    ? "暂时无法刷新订阅，稍后自动重试。" : value;
  return i18n.t(`youtube.${source}`, { defaultValue: source, ...values });
}
