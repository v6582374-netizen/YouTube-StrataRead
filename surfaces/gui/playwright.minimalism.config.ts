import { defineConfig, devices } from "@playwright/test";
import base from "./playwright.config";

// Exercise the real object backend in both Chromium and the macOS WebKit engine.
export default defineConfig({
  ...base,
  testMatch: "minimalism.spec.ts",
  workers: 1,
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "webkit", use: { ...devices["Desktop Safari"] } },
  ],
});
