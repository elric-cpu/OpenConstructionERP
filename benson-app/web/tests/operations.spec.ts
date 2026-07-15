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
  await page.route("**/api/benson/v1/leads?limit=100*", async (route) => {
    await route.fulfill({
      json: {
        leads: [
          {
            id: "lead-1",
            status: "new",
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
  await page.route("**/api/benson/v1/settings/notifications", (route) =>
    route.fulfill({ json: { email_enabled: true, sms_enabled: false, sms_configured: true } }),
  );
  await page.goto("/");
  await expect(page.getByText("Harney County homeowner")).toBeVisible();
  await expect(page.getByText("Window replacement · Burns")).toBeVisible();
  await expect(page.getByText("urgent", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
});

test("owners can opt in to emergency SMS from settings", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("benson-google-credential", "owner-token"));
  await page.route("**/api/v1/dashboard", (route) =>
    route.fulfill({
      json: {
        metrics: { new_leads: 0, active_jobs: 0, open_tasks: 0, unbilled_work: 0 },
        attention: [],
        schedule: [],
        jobs: [],
      },
    }),
  );
  await page.route("**/api/benson/v1/leads?limit=100*", (route) => route.fulfill({ json: { leads: [] } }));
  let smsEnabled = false;
  await page.route("**/api/benson/v1/settings/notifications", async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer owner-token");
    if (route.request().method() === "PATCH") {
      smsEnabled = (route.request().postDataJSON() as { sms_enabled: boolean }).sms_enabled;
    }
    await route.fulfill({
      json: { email_enabled: true, sms_enabled: smsEnabled, sms_configured: true },
    });
  });

  await page.goto("/");
  const toggle = page.getByRole("checkbox", { name: "Emergency SMS alerts" });
  await expect(toggle).not.toBeChecked();
  await toggle.check();
  await expect(toggle).toBeChecked();
  await expect(page.getByText("Saved", { exact: true })).toBeVisible();
});

test("staff can operate a lead and create a fact-scoped AI draft", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("benson-google-credential", "test-token"));
  const detail = {
    id: "lead-1",
    status: "new",
    priority: "urgent",
    name: "Harney County homeowner",
    phone: "458-555-0100",
    email: "homeowner@example.com",
    service_type: "Window replacement",
    city: "Burns",
    created_at: "2026-07-14T12:00:00Z",
    assigned_to: null,
    payload: {
      address: "123 Main St",
      timeline: "This month",
      message: "Two windows need review.",
      access_notes: "Use the side gate.",
    },
    attachments: [
      {
        id: "attachment-1",
        original_name: "window.jpg",
        content_type: "image/jpeg",
        size_bytes: 1200,
        created_at: "2026-07-14T12:05:00Z",
      },
    ],
    notes: [],
    audit_events: [
      {
        id: "audit-1",
        event: "lead.accepted",
        actor: "benson-website",
        payload: {},
        occurred_at: "2026-07-14T12:00:00Z",
      },
    ],
  };
  await page.route("**/api/v1/dashboard", (route) =>
    route.fulfill({
      json: {
        metrics: { new_leads: 1, active_jobs: 0, open_tasks: 0, unbilled_work: 0 },
        attention: [],
        schedule: [],
        jobs: [],
      },
    }),
  );
  await page.route("**/api/benson/v1/leads?limit=100*", (route) => route.fulfill({ json: { leads: [detail] } }));
  await page.route("**/api/benson/v1/settings/notifications", (route) => route.fulfill({ status: 403 }));
  await page.route("**/api/benson/v1/leads/lead-1", async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer test-token");
    if (route.request().method() === "PATCH") {
      const change = route.request().postDataJSON() as Record<string, string>;
      if (change.note)
        detail.notes.unshift({
          id: "note-1",
          author: "office@bensonhomesolutions.com",
          body: change.note,
          created_at: "2026-07-14T13:00:00Z",
        });
      Object.assign(detail, change);
    }
    await route.fulfill({ json: detail });
  });
  await page.route("**/api/benson/v1/ai/skills", (route) =>
    route.fulfill({
      json: {
        skills: [
          {
            id: "historical-cost-analyzer",
            label: "Compare historical costs",
            description: "Compare supplied costs.",
            risk: "internal",
          },
        ],
      },
    }),
  );
  await page.route("**/api/benson/v1/ai/runs", async (route) => {
    const request = route.request().postDataJSON();
    expect(request.record_context.lead.id).toBe("lead-1");
    expect(request.record_context.lead.intake.message).toBe("Two windows need review.");
    await route.fulfill({ json: { status: "completed", summary: "Call the homeowner and confirm measurements." } });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /Harney County homeowner/ }).click();
  await expect(page.getByRole("heading", { name: "Harney County homeowner" })).toBeVisible();
  await expect(page.getByText("Two windows need review.")).toBeVisible();
  await expect(page.getByRole("button", { name: /window.jpg/ })).toBeVisible();
  await page.getByLabel("New lead note").fill("Called and left a voicemail.");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(page.getByText("Called and left a voicemail.")).toBeVisible();
  await page.getByRole("button", { name: "Create draft" }).click();
  await expect(page.getByText("Call the homeowner and confirm measurements.")).toBeVisible();
  const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
  expect(results.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? ""))).toEqual([]);
});
