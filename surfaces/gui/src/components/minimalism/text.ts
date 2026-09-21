import i18n from "i18next";

/** Keep the module's copy in the host locale, preserving inline text spacing. */
export function mt(value: string): string {
  const key = value.trim();
  if (!key) return value;
  return value.replace(key, i18n.t(`minimalism.${key}`, { defaultValue: key }));
}
