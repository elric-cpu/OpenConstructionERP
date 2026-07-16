import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/benson/v1/session", (route) =>
    route.fulfill({
      json: {
        kind: "staff",
        email: "office@bensonhomesolutions.com",
        role: "office",
        default_view: "overview",
        employee: null,
      },
    }),
  );
  await page.route("**/api/benson/v1/customers?query=*", (route) => route.fulfill({ json: [] }));
});

async function mockEmptyWorkspace(page: import("@playwright/test").Page) {
  await page.addInitScript(() => sessionStorage.setItem("benson-google-credential", "test-token"));
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
  await page.route("**/api/benson/v1/settings/notifications", (route) => route.fulfill({ status: 403 }));
}

test("operations dashboard is responsive and accessible", async ({ page }) => {
  await mockEmptyWorkspace(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Good morning." })).toBeVisible();
  await expect(page.getByText("Benson Assistant")).toBeVisible();
  await expect(page.locator('link[rel="icon"]')).toHaveAttribute("href", "/benson-enterprises-logo.svg");
  await expect(page.getByRole("img", { name: "Benson Home Solutions" })).toHaveAttribute(
    "src",
    "/benson-enterprises-logo.svg",
  );
  await expect(page.getByText("BH", { exact: true })).toHaveCount(0);
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
  await expect(page.getByText("Jobs", { exact: true })).toBeVisible();
  await expect(page.getByText("Later", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Close menu" }).click();
  await expect(page.locator("aside")).not.toHaveClass(/open/);
});

test("sidebar navigation switches launch views and does not route to deferred modules", async ({ page }) => {
  await mockEmptyWorkspace(page);
  await page.route("**/api/benson/v1/jobs", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/benson/v1/estimates?status=accepted", (route) => route.fulfill({ json: [] }));
  await page.goto("/#overview");
  const overview = page.getByRole("link", { name: "Overview" });
  const leads = page.getByRole("link", { name: "Leads" });
  const jobs = page.getByRole("link", { name: "Jobs" });
  const mobile = (page.viewportSize()?.width ?? 1_000) <= 900;

  await expect(overview).toHaveAttribute("aria-current", "page");
  if (mobile) await page.getByRole("button", { name: "Open menu" }).click();
  await leads.click();
  await expect(page).toHaveURL(/#leads$/);
  await expect(leads).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "Leads" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Good morning." })).not.toBeVisible();

  if (mobile) await page.getByRole("button", { name: "Open menu" }).click();
  await jobs.click();
  await expect(page).toHaveURL(/#jobs$/);
  await expect(jobs).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("heading", { name: "Jobs", exact: true })).toBeVisible();

  if (mobile) await page.getByRole("button", { name: "Open menu" }).click();
  const schedule = page.getByText("Schedule", { exact: true });
  await expect(schedule).toBeVisible();
  await expect(schedule.locator("..")).toHaveClass(/nav-disabled/);
  await expect(page.getByRole("link", { name: "Schedule" })).toHaveCount(0);
  await expect(page).toHaveURL(/#jobs$/);
  await expect(jobs).toHaveAttribute("aria-current", "page");
});

test("staff can create and edit a persisted customer", async ({ page }) => {
  await mockEmptyWorkspace(page);
  let customer = {
    id: "customer-1",
    name: "Fields Property Owner",
    company: "",
    phone: "541-555-0105",
    email: "fields@example.com",
    billing_address: "",
    service_address: "1 Fields Highway",
    city: "Fields",
    state: "OR",
    zip_code: "97710",
    notes: "",
    status: "active",
    source_lead_id: null,
    created_at: "2026-07-16T00:00:00Z",
    updated_at: "2026-07-16T00:00:00Z",
  };
  await page.route("**/api/benson/v1/customers", async (route) => {
    expect(route.request().method()).toBe("POST");
    customer = { ...customer, ...(route.request().postDataJSON() as typeof customer) };
    await route.fulfill({ status: 201, json: customer });
  });
  await page.route("**/api/benson/v1/customers/customer-1", async (route) => {
    expect(route.request().method()).toBe("PATCH");
    customer = { ...customer, ...(route.request().postDataJSON() as typeof customer) };
    await route.fulfill({ json: customer });
  });

  await page.goto("/#customers");
  await expect(page.getByRole("link", { name: "Customers" })).toHaveAttribute("aria-current", "page");
  await page.getByRole("button", { name: "+ Add customer" }).click();
  await page.getByLabel("Customer name").fill(customer.name);
  await page.getByLabel("Phone").fill(customer.phone);
  await page.getByLabel("Email").fill(customer.email);
  await page.getByLabel("Service address").fill(customer.service_address);
  await page.getByLabel("City").fill(customer.city);
  await page.getByLabel("ZIP code").fill(customer.zip_code);
  await page.getByRole("button", { name: "Save customer" }).click();
  await expect(page.getByRole("heading", { name: customer.name })).toBeVisible();
  await page.getByRole("button", { name: "Edit" }).click();
  await page.getByLabel("Company").fill("Fields Station LLC");
  await page.getByRole("button", { name: "Save customer" }).click();
  await expect(page.getByText("Fields Station LLC")).toBeVisible();
  const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
  expect(results.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? ""))).toEqual([]);
});

test("staff create a server-totaled estimate and confirm delivery", async ({ page }) => {
  await mockEmptyWorkspace(page);
  const customer = {
    id: "customer-estimate",
    name: "Estimate Customer",
    company: "",
    phone: "541-555-0122",
    email: "estimate@example.com",
    billing_address: "",
    service_address: "10 Main Street",
    city: "Burns",
    state: "OR",
    zip_code: "97720",
    notes: "",
    status: "active",
    source_lead_id: null,
    created_at: "2026-07-16T00:00:00Z",
    updated_at: "2026-07-16T00:00:00Z",
  };
  let estimate = {
    id: "estimate-1",
    number: "EST-2026-TEST0001",
    customer_id: customer.id,
    customer_name: customer.name,
    title: "Window replacement",
    scope_notes: "",
    valid_until: "2026-08-31",
    status: "draft",
    version: 1,
    subtotal_cents: 125000,
    total_cents: 125000,
    lines: [],
    created_at: "2026-07-16T00:00:00Z",
    updated_at: "2026-07-16T00:00:00Z",
  };
  await page.route("**/api/benson/v1/customers?query=*", (route) => route.fulfill({ json: [customer] }));
  await page.route("**/api/benson/v1/estimates", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: [] });
      return;
    }
    const payload = route.request().postDataJSON() as { title: string; lines: unknown[] };
    estimate = { ...estimate, title: payload.title, lines: payload.lines };
    await route.fulfill({ status: 201, json: estimate });
  });
  await page.route("**/api/benson/v1/estimates/estimate-1/transition", async (route) => {
    const payload = route.request().postDataJSON() as { status: string; external_delivery_confirmed: boolean };
    if (payload.status === "sent") expect(payload.external_delivery_confirmed).toBe(true);
    estimate = { ...estimate, status: payload.status };
    await route.fulfill({ json: estimate });
  });
  await page.route("**/api/benson/v1/estimates/estimate-1", async (route) => {
    expect(route.request().method()).toBe("PATCH");
    const payload = route.request().postDataJSON() as { title: string };
    estimate = { ...estimate, title: payload.title, version: 2 };
    await route.fulfill({ json: estimate });
  });

  await page.goto("/#estimates");
  await expect(page.getByRole("heading", { name: "Estimates", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "+ New estimate" }).click();
  await page.getByLabel("Estimate title").fill(estimate.title);
  await page.getByLabel("Valid until").fill(estimate.valid_until);
  await page.getByLabel("Description").fill("High-desert rated window");
  await page.getByLabel("Unit price").fill("1250.00");
  await page.getByRole("button", { name: "Save draft" }).click();
  await expect(page.getByRole("heading", { name: estimate.title })).toBeVisible();
  await expect(page.getByText("$1,250.00")).toBeVisible();
  await page.getByRole("button", { name: "Edit" }).click();
  await page.getByLabel("Estimate title").fill("Revised window replacement");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByRole("heading", { name: "Revised window replacement" })).toBeVisible();
  await page.getByRole("button", { name: "Mark ready" }).click();
  await expect(page.getByText("ready", { exact: true })).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Mark delivered" }).click();
  await expect(page.getByText("sent", { exact: true })).toBeVisible();
  const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
  expect(results.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? ""))).toEqual([]);
});

test("staff convert an accepted estimate and deliver the planned job", async ({ page }) => {
  await mockEmptyWorkspace(page);
  const estimate = {
    id: "estimate-accepted",
    number: "EST-2026-ACCEPTED",
    customer_id: "customer-job",
    customer_name: "Fields Property Owner",
    title: "Frontier window installation",
    scope_notes: "Install high-desert rated windows.",
    valid_until: "2026-08-31",
    status: "accepted",
    version: 3,
    subtotal_cents: 420000,
    total_cents: 420000,
    lines: [],
    created_at: "2026-07-16T00:00:00Z",
    updated_at: "2026-07-16T00:00:00Z",
  };
  let job = {
    id: "job-1",
    number: "JOB-2026-TEST0001",
    estimate_id: estimate.id,
    estimate_number: estimate.number,
    customer_id: estimate.customer_id,
    customer_name: estimate.customer_name,
    title: estimate.title,
    scope_snapshot: estimate.scope_notes,
    contract_value_cents: estimate.total_cents,
    status: "planned",
    target_start: "2026-08-03",
    target_completion: "2026-08-05",
    assigned_to: "elric@bensonhomesolutions.com",
    site_address: "1 Fields Highway, Fields, OR 97710",
    created_at: "2026-07-16T00:00:00Z",
    updated_at: "2026-07-16T00:00:00Z",
  };
  let jobs: (typeof job)[] = [];
  await page.route("**/api/benson/v1/estimates?status=accepted", (route) =>
    route.fulfill({ json: jobs.length ? [] : [estimate] }),
  );
  await page.route("**/api/benson/v1/jobs", (route) => route.fulfill({ json: jobs }));
  await page.route(`**/api/benson/v1/jobs/from-estimate/${estimate.id}`, async (route) => {
    expect(route.request().method()).toBe("POST");
    const plan = route.request().postDataJSON() as Partial<typeof job>;
    job = { ...job, ...plan };
    jobs = [job];
    await route.fulfill({ status: 201, json: job });
  });
  await page.route("**/api/benson/v1/jobs/job-1", async (route) => {
    expect(route.request().method()).toBe("PATCH");
    const plan = route.request().postDataJSON() as Partial<typeof job>;
    job = { ...job, ...plan };
    jobs = [job];
    await route.fulfill({ json: job });
  });
  await page.route("**/api/benson/v1/jobs/job-1/transition", async (route) => {
    expect(route.request().method()).toBe("POST");
    const payload = route.request().postDataJSON() as { status: typeof job.status; note: string };
    if (payload.status === "completed") expect(payload.note).toBe("Work verified complete");
    job = { ...job, status: payload.status };
    jobs = [job];
    await route.fulfill({ json: job });
  });

  await page.goto("/#jobs");
  await expect(page.getByRole("link", { name: "Jobs" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByText(estimate.title, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Create job" }).click();
  await page.getByLabel("Target start").fill(job.target_start);
  await page.getByLabel("Target completion").fill(job.target_completion);
  await page.getByLabel("Assigned staff email").fill(job.assigned_to);
  await page.getByLabel("Site address").fill(job.site_address);
  await page.getByRole("button", { name: "Create planned job" }).click();
  await expect(page.getByText("planned", { exact: true })).toBeVisible();
  await expect(page.getByText("$4,200.00")).toBeVisible();

  await page.getByRole("button", { name: "Edit plan" }).click();
  await page.getByLabel("Job title").fill("Revised frontier window installation");
  await page.getByRole("button", { name: "Save job plan" }).click();
  await expect(page.getByRole("heading", { name: "Revised frontier window installation" })).toBeVisible();

  await page.getByRole("button", { name: "Start job" }).click();
  await expect(page.getByText("active", { exact: true })).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept("Work verified complete"));
  await page.getByRole("button", { name: "Complete job" }).click();
  await expect(page.getByText("completed", { exact: true })).toBeVisible();
  const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
  expect(results.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? ""))).toEqual([]);
});

for (const role of ["field", "accounting"] as const) {
  test(`${role} staff enter the scoped Jobs workspace without CRM access`, async ({ page }) => {
    await page.addInitScript(() => sessionStorage.setItem("benson-google-credential", "role-token"));
    await page.unroute("**/api/benson/v1/session");
    await page.route("**/api/benson/v1/session", (route) =>
      route.fulfill({
        json: {
          kind: "staff",
          email: `${role}@bensonhomesolutions.com`,
          role,
          default_view: "overview",
          employee: null,
        },
      }),
    );
    let requestedCrm = false;
    page.on("request", (request) => {
      if (/\/leads|\/customers|\/estimates/.test(new URL(request.url()).pathname)) requestedCrm = true;
    });
    await page.route("**/api/benson/v1/jobs", (route) =>
      route.fulfill({
        json: [
          {
            id: "role-job",
            number: "JOB-2026-ROLE",
            estimate_id: "estimate-role",
            estimate_number: "EST-2026-ROLE",
            customer_id: "customer-role",
            customer_name: "Assigned Customer",
            title: "Assigned field work",
            scope_snapshot: "",
            contract_value_cents: 100000,
            status: "planned",
            target_start: null,
            target_completion: null,
            assigned_to: role === "field" ? "field@bensonhomesolutions.com" : null,
            site_address: "Burns, OR",
            created_at: "2026-07-16T00:00:00Z",
            updated_at: "2026-07-16T00:00:00Z",
          },
        ],
      }),
    );

    await page.goto("/#overview");
    await expect(page).toHaveURL(/#jobs$/);
    await expect(page.getByRole("heading", { name: "Jobs", exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: "Jobs" })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("link", { name: "Leads" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Edit plan" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Create job" })).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Start job" })).toHaveCount(role === "field" ? 1 : 0);
    expect(requestedCrm).toBe(false);
  });
}

test("unsupported legacy hashes normalize to the overview", async ({ page }) => {
  await mockEmptyWorkspace(page);
  await page.goto("/#schedule");
  await expect(page).toHaveURL(/#overview$/);
  await expect(page.getByRole("link", { name: "Overview" })).toHaveAttribute("aria-current", "page");
});

test("empty states never fabricate operational records", async ({ page }) => {
  await mockEmptyWorkspace(page);
  await page.goto("/");
  await expect(page.getByText("You’re caught up")).toBeVisible();
  await expect(page.getByText("No active jobs yet")).toBeVisible();
  await expect(page.getByText("Schedule is outside launch scope")).toBeVisible();
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
            source: "Website",
            is_spam: false,
            spam_reason: null,
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
  await expect(page.getByText("Source: Website")).toBeVisible();
  await expect(page.getByLabel("Filter spam leads")).toHaveValue("active");
  await page.getByLabel("Filter leads by source").selectOption("Website");
  await expect(page.getByText("Harney County homeowner")).toBeVisible();
  await expect(page.getByRole("button", { name: "Sign out" })).toBeVisible();
});

test("sign out invalidates in-flight authenticated responses", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("benson-google-credential", "test-token"));
  let releaseResponses: () => void = () => undefined;
  const delayed = new Promise<void>((resolve) => {
    releaseResponses = resolve;
  });
  await page.route("**/api/v1/dashboard", async (route) => {
    await delayed;
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
    await delayed;
    await route.fulfill({
      json: {
        leads: [
          {
            id: "private-lead",
            status: "new",
            priority: "normal",
            name: "Private homeowner",
            service_type: "Repair",
            city: "Burns",
            created_at: "2026-07-14T12:00:00Z",
          },
        ],
      },
    });
  });
  await page.route("**/api/benson/v1/settings/notifications", async (route) => {
    await delayed;
    await route.fulfill({ json: { email_enabled: true, sms_enabled: false, sms_configured: false } });
  });

  await page.goto("/");
  await page.getByRole("button", { name: "Sign out" }).click();
  releaseResponses();

  await expect(page.getByRole("heading", { name: /Sign in with your Benson/ })).toBeVisible();
  await expect(page.getByText("Private homeowner")).not.toBeVisible();
  await expect(page.getByText("System ready")).not.toBeVisible();
});

test("owners can opt in to client SMS and emergency alerts", async ({ page }) => {
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
  const toggle = page.getByRole("checkbox", {
    name: "Client SMS/MMS and emergency alerts",
  });
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
    source: "Google",
    is_spam: false,
    spam_reason: null,
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
    if (route.request().method() === "DELETE") {
      await route.fulfill({ status: 204 });
      return;
    }
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
  await page.route("**/api/benson/v1/staff", (route) =>
    route.fulfill({
      json: {
        staff: [
          { email: "elric@bensonhomesolutions.com", display_name: "Elric", role: "owner" },
          { email: "office@bensonhomesolutions.com", display_name: "Benson Office", role: "office" },
        ],
      },
    }),
  );
  await page.route("**/api/benson/v1/ai/runs", async (route) => {
    const request = route.request().postDataJSON();
    expect(request.lead_id).toBe("lead-1");
    await route.fulfill({ json: { status: "completed", summary: "Call the homeowner and confirm measurements." } });
  });

  await page.goto("/");
  await page.getByRole("button", { name: /Harney County homeowner/ }).click();
  await expect(page.getByRole("heading", { name: "Harney County homeowner" })).toBeVisible();
  await expect(page.getByText("Two windows need review.")).toBeVisible();
  await expect(page.getByRole("button", { name: /window.jpg/ })).toBeVisible();
  await expect(page.getByLabel("Lead source")).toHaveValue("Google");
  await page.getByLabel("Name").fill("Edited homeowner");
  await page.getByLabel("Lead source").fill("Referral");
  await page.getByRole("button", { name: "Save lead details" }).click();
  await expect(page.getByRole("heading", { name: "Edited homeowner" })).toBeVisible();
  await page.getByRole("button", { name: "Mark as spam" }).click();
  await expect(page.getByRole("button", { name: "Not spam" })).toBeVisible();
  await expect(page.getByLabel("Assigned to")).toHaveValue("");
  await expect(page.getByLabel("Assigned to").getByRole("option", { name: "Elric" })).toHaveAttribute(
    "value",
    "elric@bensonhomesolutions.com",
  );
  await page.getByLabel("Assigned to").selectOption("elric@bensonhomesolutions.com");
  await page.getByRole("button", { name: "Save assignment" }).click();
  await expect(page.getByLabel("Assigned to")).toHaveValue("elric@bensonhomesolutions.com");
  await page.getByLabel("New lead note").fill("Called and left a voicemail.");
  await page.getByRole("button", { name: "Add note" }).click();
  await expect(page.getByText("Called and left a voicemail.")).toBeVisible();
  await page.getByRole("button", { name: "Create draft" }).click();
  await expect(page.getByText("Call the homeowner and confirm measurements.")).toBeVisible();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "Delete lead" }).click();
  await expect(page.getByRole("heading", { name: "Leads" })).toBeVisible();
  const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
  expect(results.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? ""))).toEqual([]);
});
