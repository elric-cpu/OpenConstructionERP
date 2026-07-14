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

test("authenticated staff see persisted website leads", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("benson-google-credential", "test-token"));
  await page.route("**/api/v1/dashboard", async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer test-token");
    await route.fulfill({
      json: {
        metrics: { new_leads: 1, active_jobs: 0, open_tasks: 0, unbilled_work: 0 },
        attention: [],
        schedule: [],
        jobs: [],
      },
    });
  });
  await page.route("**/api/benson/v1/leads?limit=6", async (route) => {
    await route.fulfill({
      json: {
        leads: [
          {
            id: "lead-1",
            priority: "urgent",
            name: "Harney County homeowner",
            service_type: "Window replacement",
            city: "Burns",
            created_at: "2026-07-14T12:00:00Z",
          },
        ],
      },
    });
  });
  await page.goto("/");
  await expect(page.getByText("Harney County homeowner")).toBeVisible();
  await expect(page.getByText("Window replacement · Burns")).toBeVisible();
  await expect(page.getByText("urgent", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
});
