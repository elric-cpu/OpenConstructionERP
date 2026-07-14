import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test("operations dashboard is responsive and accessible", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Good morning." })).toBeVisible();
  await expect(page.getByText("Benson Assistant")).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
  const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
  expect(results.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? ""))).toEqual([]);
});

test("mobile rail opens and exposes operations navigation", async ({ page }, testInfo) => {
  test.skip(!testInfo.project.name.startsWith("mobile"), "mobile-only interaction");
  await page.goto("/");
  await page.getByRole("button", { name: "Open menu" }).click();
  await expect(page.getByRole("link", { name: "Jobs", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Close menu" }).click();
  await expect(page.locator("aside")).not.toHaveClass(/open/);
});

test("empty states never fabricate operational records", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("You’re caught up")).toBeVisible();
  await expect(page.getByText("No active jobs yet")).toBeVisible();
  await expect(page.getByText("No visits scheduled")).toBeVisible();
});
