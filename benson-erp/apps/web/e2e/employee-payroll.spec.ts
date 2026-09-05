import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const organization = process.env.E2E_ORGANIZATION ?? "benson-e2e";
const managerEmail = process.env.E2E_EMAIL ?? "e2e@bensonhomesolutions.com";
const managerPassword = process.env.E2E_PASSWORD;
const employeePassword = "BensonEmployee!E2E-Temp";

type RecordShape = { id: string; version: number; [key: string]: unknown };

test("activated employee time flows through approval, payroll, and job cost", async ({ page, request }) => {
  test.setTimeout(120_000);
  if (!managerPassword) throw new Error("E2E_PASSWORD must be set for real-stack browser tests");
  const managerToken = await apiLogin(request, managerEmail, managerPassword);
  const suffix = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
  const employee = await createActivatedEmployee(request, managerToken, suffix);
  const projects = await api<RecordShape[]>(request, managerToken, "GET", "/projects");
  expect(projects.length).toBeGreaterThan(0);
  const project = projects[0];
  const workDate = await availableWorkDate(request, managerToken);

  await login(page, String(employee.company_email), employeePassword);
  await page.getByRole("link", { name: "Time" }).click();
  await expect(page.getByRole("heading", { name: "Daily time" })).toBeVisible();
  await expect(page.getByLabel("Employee")).toBeDisabled();
  await page.getByRole("combobox", { name: "Project", exact: true }).selectOption(project.id);
  await page.getByLabel("Work date").fill(workDate);
  await page.getByLabel("Work performed").fill(`Certified payroll E2E ${suffix}`);
  const entryResponse = page.waitForResponse((response) =>
    response.request().method() === "POST" && response.url().endsWith("/api/v1/time-entries"),
  );
  await page.getByRole("button", { name: "Save daily time" }).click();
  const entry = (await (await entryResponse).json()) as RecordShape;
  const row = page.getByText(`Certified payroll E2E ${suffix}`).locator("xpath=ancestor::li");
  await row.getByRole("button", { name: "Certify my time" }).click();
  await expect(row).toContainText("CERTIFIED");

  await page.getByRole("button", { name: "Sign out" }).click();
  await login(page, managerEmail, managerPassword);
  await page.getByRole("link", { name: "Time" }).click();
  const managerRow = page.getByText(`Certified payroll E2E ${suffix}`).locator("xpath=ancestor::li");
  await managerRow.getByRole("button", { name: "Approve" }).click();
  await expect(managerRow).toContainText("APPROVED");

  const period = await configurePayroll(request, managerToken, employee, project, entry);
  const payrollExport = await generateExport(request, managerToken, period);
  const exportedPeriod = (await api<RecordShape[]>(
    request, managerToken, "GET", "/payroll/periods",
  )).find((item) => item.id === period.id)!;
  const imported = await importResults(
    request, managerToken, exportedPeriod, payrollExport, entry, suffix,
  );
  const reconciliation = await api<RecordShape>(
    request,
    managerToken,
    "GET",
    `/payroll/result-imports/${imported.id}/reconciliation`,
  );
  expect(reconciliation.job_cost_count).toBe(1);
  expect(Number(reconciliation.job_cost_total)).toBeGreaterThan(0);
  const reconciled = await api<RecordShape>(
    request,
    managerToken,
    "POST",
    `/payroll/result-imports/${imported.id}/reconcile`,
    undefined,
    { "If-Match": String(imported.version) },
  );
  expect(reconciled.status).toBe("RECONCILED");

  await page.goto("/payroll");
  await expect(page.getByRole("heading", { name: "Payroll review" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Employee source drill-down" })).toBeVisible();
  await expect(page.getByText(String(entry.id).slice(0, 8), { exact: true })).toBeVisible();
  await expect(page.getByText("Job-cost rows").locator("..")).toContainText("1");

  const duplicate = await request.post(`/api/v1/payroll/periods/${period.id}/exports`, {
    headers: authHeaders(managerToken, { "If-Match": String(exportedPeriod.version) }),
    data: { format: "CSV", include_sensitive_fields: true },
  });
  expect(duplicate.status()).toBe(409);
});

async function createActivatedEmployee(
  request: APIRequestContext,
  token: string,
  suffix: string,
) {
  const employee = await api<RecordShape>(request, token, "POST", "/employees", {
    employee_number: `PAY-${suffix}`,
    first_name: "Payroll",
    last_name: "Worker",
    personal_email: `payroll-${suffix}@example.com`,
    company_username: `payroll.${suffix}`.slice(0, 78),
    hire_date: isoDate(0),
  });
  await api(request, token, "POST", `/employees/${employee.id}/approve`, {
    reason: "Playwright payroll workflow approval",
  }, { "If-Match": String(employee.version) });
  let preview: { activation_url: string } | undefined;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const response = await request.get(`/api/v1/employees/${employee.id}/activation-preview`, {
      headers: authHeaders(token),
    });
    if (response.ok()) {
      preview = (await response.json()) as { activation_url: string };
      break;
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  expect(preview?.activation_url).toBeTruthy();
  const activationToken = new URL(preview!.activation_url).hash.replace("#token=", "");
  await api(request, null, "POST", "/auth/employee-activations/complete", {
    token: activationToken,
    password: employeePassword,
  });
  return api<RecordShape>(request, token, "GET", `/employees/${employee.id}`);
}

async function configurePayroll(
  request: APIRequestContext,
  token: string,
  employee: RecordShape,
  project: RecordShape,
  entry: RecordShape,
) {
  const period = await api<RecordShape>(request, token, "POST", "/payroll/periods", {
    period_start: entry.work_date,
    period_end: entry.work_date,
    pay_date: isoDate(5),
    workweek_definition: "Monday through Sunday",
    provider: "GENERIC",
  });
  await api(request, token, "POST", "/payroll/pay-rates", {
    employee_id: employee.id,
    effective_from: entry.work_date,
    base_rate: "25.0000",
    overtime_rate: "37.5000",
    double_time_rate: "50.0000",
    fringe_rate: "2.0000",
    cash_in_lieu_rate: "0.0000",
  });
  const existingMappings = await api<RecordShape[]>(
    request, token, "GET", "/payroll/mappings?provider=GENERIC",
  );
  for (const [mapping_type, internal_key, external_code] of [
    ["EMPLOYEE", employee.id, `PROVIDER-${employee.id}`],
    ["EARNING", "REGULAR", "REG"],
    ["PROJECT", project.id, `JOB-${project.id}`],
  ]) {
    const exists = existingMappings.some((mapping) =>
      mapping.mapping_type === mapping_type && mapping.internal_key === internal_key &&
      String(mapping.effective_from) <= String(entry.work_date) &&
      (!mapping.effective_to || String(mapping.effective_to) >= String(entry.work_date)),
    );
    if (exists) continue;
    await api(request, token, "POST", "/payroll/mappings", {
      provider: "GENERIC", mapping_type, internal_key, external_code,
      effective_from: entry.work_date, configuration: {},
    });
  }
  const preview = await api<RecordShape>(request, token, "GET", `/payroll/periods/${period.id}/preview`);
  expect(preview.ready_to_lock).toBe(true);
  expect((preview.employees as RecordShape[])[0].source_time_entry_ids).toContain(entry.id);
  let current = period;
  for (const target_status of ["EMPLOYEE_REVIEW", "SUPERVISOR_REVIEW", "PAYROLL_REVIEW", "LOCKED"]) {
    current = await api(request, token, "POST", `/payroll/periods/${current.id}/transitions`, {
      target_status, reason: "Playwright verified payroll stage",
    }, { "If-Match": String(current.version) });
  }
  return current;
}

async function generateExport(request: APIRequestContext, token: string, period: RecordShape) {
  return api<RecordShape>(request, token, "POST", `/payroll/periods/${period.id}/exports`, {
    format: "CSV", include_sensitive_fields: true,
  }, { "If-Match": String(period.version) });
}

async function importResults(
  request: APIRequestContext, token: string, period: RecordShape,
  payrollExport: RecordShape, entry: RecordShape, suffix: string,
) {
  return api<RecordShape>(request, token, "POST", `/payroll/periods/${period.id}/result-imports`, {
    payroll_export_id: payrollExport.id,
    provider_reference: `PAY-${suffix}`,
    lines: [{
      time_entry_id: entry.id, provider_employee_id: `PROVIDER-${entry.employee_id}`,
      provider_payroll_id: `RUN-${suffix}`, work_date: entry.work_date, pay_date: isoDate(5),
      regular_hours: "8.00", overtime_hours: "0.00", double_time_hours: "0.00",
      travel_hours: "0.00", leave_hours: "0.00", indirect_hours: "0.00",
      base_rate: "25.0000", overtime_rate: "37.5000", double_time_rate: "50.0000",
      gross_wages: "200.00", employer_taxes: "18.00", employee_deductions: "20.00",
      employer_benefits: "10.00", workers_compensation: "4.00", fringe_benefits: "16.00",
      net_pay: "180.00", is_adjustment: false,
    }],
  }, { "If-Match": String(period.version) });
}

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Organization").fill(organization);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Lead to project" })).toBeVisible();
}

async function apiLogin(request: APIRequestContext, email: string, password: string) {
  const response = await request.post("/api/v1/auth/login", {
    data: { organization, email, password, device_name: "Playwright payroll API" },
  });
  expect(response.ok()).toBeTruthy();
  return String((await response.json()).access_token);
}

async function api<T>(
  request: APIRequestContext, token: string | null, method: "GET" | "POST", path: string,
  data?: unknown, extraHeaders?: Record<string, string>,
) {
  const response = await request.fetch(`/api/v1${path}`, {
    method, headers: authHeaders(token, extraHeaders), data,
  });
  expect(response.ok(), `${method} ${path}: ${await response.text()}`).toBeTruthy();
  return (await response.json()) as T;
}

function authHeaders(token: string | null, extra: Record<string, string> = {}) {
  return token ? { Authorization: `Bearer ${token}`, ...extra } : extra;
}

function isoDate(daysFromToday: number) {
  return new Date(Date.now() + daysFromToday * 86_400_000).toISOString().slice(0, 10);
}

async function availableWorkDate(request: APIRequestContext, token: string) {
  const periods = await api<RecordShape[]>(request, token, "GET", "/payroll/periods");
  for (let offset = 0; offset >= -13; offset -= 1) {
    const candidate = isoDate(offset);
    const overlaps = periods.some((period) =>
      String(period.period_start) <= candidate && String(period.period_end) >= candidate,
    );
    if (!overlaps) return candidate;
  }
  throw new Error("No payroll-test work date is available in the recent time-entry window");
}
