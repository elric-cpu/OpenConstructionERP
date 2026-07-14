import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "./tests",
  fullyParallel: true,
  retries: 1,
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: process.env.CI ? "http://127.0.0.1:4173" : "http://benson-ai:4173",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  webServer: { command: "npm run dev -- --port 4173", url: "http://127.0.0.1:4173", reuseExistingServer: false },
  projects: [
    { name: "desktop-chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "mobile-chromium", use: { ...devices["Pixel 7"] } },
  ],
});
