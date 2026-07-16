import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const ownerSession = {
  kind: "staff",
  email: "elric@bensonhomesolutions.com",
  role: "owner",
  default_view: "overview",
  employee: null,
};

async function mockOwnerPortal(page: import("@playwright/test").Page) {
  await page.addInitScript(() => sessionStorage.setItem("benson-google-credential", "owner-token"));
  await page.route("**/api/benson/v1/session", (route) => route.fulfill({ json: ownerSession }));
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
  await page.route("**/api/benson/v1/customers?query=*", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/benson/v1/settings/notifications", (route) => route.fulfill({ status: 403 }));
}

test("owner creates an unlicensed new hire and queues the invite", async ({ page }) => {
  await mockOwnerPortal(page);
  const employees: Record<string, unknown>[] = [];
  await page.route("**/api/benson/v1/employees", async (route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ json: employees });
      return;
    }
    const request = route.request().postDataJSON() as Record<string, unknown>;
    expect(request.workspace_unlicensed_confirmed).toBe(true);
    expect(request.invite_delivery_email).toBe("newhire@example.com");
    const employee = {
      ...request,
      id: "employee-1",
      status: "draft",
      workspace_account_status: "unlicensed_attested",
      workspace_license_policy: "no_paid_license",
      created_at: "2026-07-16T12:00:00Z",
    };
    employees.push(employee);
    await route.fulfill({ status: 201, json: employee });
  });
  await page.route("**/api/benson/v1/employees/employee-1/invite", async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer owner-token");
    await route.fulfill({
      status: 202,
      json: {
        id: "invite-1",
        employee_id: "employee-1",
        status: "pending_delivery",
        expires_at: "2026-07-19T12:00:00Z",
      },
    });
  });

  await page.goto("/#employees");
  await expect(page.getByRole("heading", { name: "New hires" })).toBeVisible();
  await page.getByLabel("Full name").fill("Morgan Builder");
  await page.getByLabel("Workspace login").fill("morgan@bensonhomesolutions.com");
  await page.getByLabel("Invite delivery email").fill("newhire@example.com");
  await page.getByLabel("Start date").fill("2026-08-03");
  await page.getByLabel(/I confirmed this account/).check();
  await page.getByRole("button", { name: "Create new hire" }).click();
  await expect(page.getByText("Morgan Builder")).toBeVisible();
  await expect(page.getByText("No paid license", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Send invite" }).click();
  await expect(page.getByText("invited", { exact: true })).toBeVisible();
  const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
  expect(results.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? ""))).toEqual([]);
});

test("employee lands on Tasks and submits encrypted evidence", async ({ page }) => {
  await page.addInitScript(() => sessionStorage.setItem("benson-google-credential", "employee-token"));
  await page.route("**/api/benson/v1/session", (route) =>
    route.fulfill({
      json: {
        kind: "employee",
        email: "morgan@bensonhomesolutions.com",
        role: "field",
        default_view: "tasks",
        employee: {
          id: "employee-1",
          name: "Morgan Builder",
          email: "morgan@bensonhomesolutions.com",
          invite_delivery_email: "newhire@example.com",
          start_date: "2026-08-03",
          work_location: "Burns, Oregon",
          classification: "employee",
          role: "field",
          federal_contract_applicability: "unknown",
          status: "active",
          workspace_account_status: "unlicensed_attested",
          workspace_license_policy: "no_paid_license",
          created_at: "2026-07-16T12:00:00Z",
        },
      },
    }),
  );
  const tasks = [
    {
      id: "task-w4",
      employee_id: "employee-1",
      requirement_id: "federal-w4",
      label: "Federal W-4",
      responsible_party: "employee",
      status: "pending",
      due_date: "2026-08-03",
      instructions: "Complete and sign your federal withholding election.",
      applicability_reason: "Required for employees.",
      evidence_required: true,
      completed_at: null,
      completed_by: null,
    },
    {
      id: "task-policy",
      employee_id: "employee-1",
      requirement_id: "policies",
      label: "Company policies",
      responsible_party: "employee",
      status: "completed",
      due_date: "2026-08-03",
      instructions: "Review company policies.",
      applicability_reason: "All employees.",
      evidence_required: false,
      completed_at: "2026-07-16T12:00:00Z",
      completed_by: "owner@bensonhomesolutions.com",
    },
  ];
  await page.route("**/api/benson/v1/onboarding/tasks", (route) =>
    route.fulfill({ json: { default_view: "tasks", tasks, progress: { completed: 1, total: 2 } } }),
  );
  await page.route("**/api/benson/v1/onboarding/documents", (route) => route.fulfill({ json: [] }));
  await page.route("**/api/benson/v1/onboarding/tasks/task-w4/evidence", async (route) => {
    expect(route.request().headers().authorization).toBe("Bearer employee-token");
    await route.fulfill({
      status: 201,
      json: {
        id: "document-1",
        employee_id: "employee-1",
        task_id: "task-w4",
        version: 1,
        original_name: "w4.pdf",
        content_type: "application/pdf",
        size_bytes: 19,
        data_classification: "highly_restricted",
        status: "active",
        created_at: "2026-07-16T12:05:00Z",
      },
    });
  });

  await page.goto("/");
  await expect(page).toHaveURL(/#tasks$/);
  await expect(page.getByRole("heading", { name: "Welcome, Morgan." })).toBeVisible();
  await expect(page.getByText("50%", { exact: true })).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: "w4.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-synthetic-test"),
  });
  await expect(page.getByText("Waiting for Benson review")).toBeVisible();
  await expect(page.getByRole("button", { name: /w4.pdf/ })).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
  const results = await new AxeBuilder({ page }).disableRules(["color-contrast"]).analyze();
  expect(results.violations.filter((item) => ["serious", "critical"].includes(item.impact ?? ""))).toEqual([]);
});

test("employee accepts an invite and is routed to Tasks", async ({ page }) => {
  await page.addInitScript(() => {
    let callback: (response: { credential: string }) => void = () => undefined;
    window.google = {
      accounts: {
        id: {
          initialize: (options) => {
            callback = options.callback;
          },
          renderButton: (element) => {
            const button = document.createElement("button");
            button.textContent = "Continue with assigned Google account";
            button.onclick = () => callback({ credential: "activation-google-credential" });
            element.append(button);
          },
        },
      },
    };
  });
  await page.route("**/api/benson/v1/auth/config", (route) =>
    route.fulfill({
      json: { client_id: "client.apps.googleusercontent.com", hosted_domain: "bensonhomesolutions.com" },
    }),
  );
  await page.route("**/api/benson/v1/onboarding/activate", async (route) => {
    expect(route.request().postDataJSON()).toEqual({
      token: "synthetic-invite-token",
      credential: "activation-google-credential",
    });
    await route.fulfill({
      json: {
        id: "employee-activation",
        name: "Alex Carpenter",
        email: "alex@bensonhomesolutions.com",
        status: "active",
      },
    });
  });
  await page.route("**/api/benson/v1/session", (route) =>
    route.fulfill({
      json: {
        kind: "employee",
        email: "alex@bensonhomesolutions.com",
        role: "field",
        default_view: "tasks",
        employee: {
          id: "employee-activation",
          name: "Alex Carpenter",
          email: "alex@bensonhomesolutions.com",
          invite_delivery_email: "alex@example.com",
          start_date: "2026-08-03",
          work_location: "Burns, Oregon",
          classification: "employee",
          role: "field",
          federal_contract_applicability: "not_applicable",
          status: "active",
          workspace_account_status: "unlicensed_attested",
          workspace_license_policy: "no_paid_license",
          created_at: "2026-07-16T12:00:00Z",
        },
      },
    }),
  );
  await page.route("**/api/benson/v1/onboarding/tasks", (route) =>
    route.fulfill({ json: { default_view: "tasks", tasks: [], progress: { completed: 0, total: 0 } } }),
  );
  await page.route("**/api/benson/v1/onboarding/documents", (route) => route.fulfill({ json: [] }));

  await page.goto("/#activate?token=synthetic-invite-token");
  await expect(page.getByRole("heading", { name: /Accept your invitation/ })).toBeVisible();
  await page.getByRole("button", { name: "Continue with assigned Google account" }).click();
  await expect(page).toHaveURL(/#tasks$/);
  await expect(page.getByRole("heading", { name: "Welcome, Alex." })).toBeVisible();
});
