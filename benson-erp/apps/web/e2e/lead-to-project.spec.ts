import { expect, test, type Page } from "@playwright/test";

const organization = process.env.E2E_ORGANIZATION ?? "benson-e2e";
const email = process.env.E2E_EMAIL ?? "e2e@bensonhomesolutions.com";
const password = process.env.E2E_PASSWORD;
const projectSuffixes = new Map<string, string>();
const employeeSuffixes = new Map<string, string>();
const employeePassword = "BensonEmployee!E2E-Temp";

test.beforeEach(async ({ page }) => {
  if (!password) {
    throw new Error("E2E_PASSWORD must be set for real-stack browser tests");
  }
  await page.goto("/login");
  await page.getByLabel("Organization").fill(organization);
  await page.getByLabel("Work email").fill(email);
  await page.getByLabel("Password").fill(password);
  await page.getByRole("button", { name: "Sign in" }).click();
  await expect(page.getByRole("heading", { name: "Lead to project" })).toBeVisible();
});

test("completes Lead to Project with a client-safe immutable proposal", async ({
  page,
}, testInfo) => {
  const suffix = uniqueSuffix(testInfo.project.name);
  projectSuffixes.set(testInfo.project.name, suffix);
  await fillWorkflow(page, suffix);

  await advance(page, "Create lead", "Qualify lead");
  await advance(page, "Qualify lead", "Create customer and property");
  await advance(page, "Create customer and property", "Start estimate");
  await advance(page, "Start estimate", "Add estimate line");
  await advance(page, "Add estimate line", "Approve estimate");
  await advance(page, "Approve estimate", "Issue proposal");

  const proposalResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      /\/api\/v1\/estimates\/[^/]+\/proposals$/.test(response.url()),
  );
  await page.getByRole("button", { name: "Issue proposal" }).click();
  const proposal = await (await proposalResponse).json();

  expect(proposal.price_snapshot).toEqual({
    selling_price: "1200.00",
    tax: "0.00",
    total: "1200.00",
  });
  for (const privateField of [
    "direct_cost",
    "pricing_rate",
    "pricing_mode",
    "margin",
    "markup",
    "unit_cost",
  ]) {
    expect(proposal.price_snapshot).not.toHaveProperty(privateField);
  }
  await expect(page.getByText(/^Document SHA-256: [a-f0-9]{64}$/)).toBeVisible();
  const proposalReview = page
    .getByRole("heading", { name: "Proposal review" })
    .locator("xpath=ancestor::section");
  await expect(proposalReview.getByText(/Direct cost|Margin|Markup|Unit cost/i)).toHaveCount(0);

  const documentResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "GET" &&
      /\/api\/v1\/proposals\/[^/]+\/document$/.test(response.url()),
  );
  await page.getByRole("button", { name: "View PDF" }).click();
  const pdf = await documentResponse;
  expect(pdf.ok()).toBeTruthy();
  expect(pdf.headers()["content-type"]).toContain("application/pdf");
  expect(pdf.headers().etag).toMatch(/^"[a-f0-9]{64}"$/);
  expect((await pdf.body()).byteLength).toBeGreaterThan(1_000);

  await page.getByLabel(/I reviewed and accept the proposal/).check();
  await advance(page, "Record acceptance", "Create contract and project");
  await page.getByRole("button", { name: "Create contract and project" }).click();

  await expect(page.getByText("Project created")).toBeVisible();
  await expect(page.getByRole("heading", { name: `E2E Addition ${suffix}` })).toBeVisible();
  await expect(page.getByText("$1200.00")).toBeVisible();
  await expect(page.getByText("1", { exact: true })).toBeVisible();
  await expect(page.getByRole("list", { name: "Workflow progress" })).toContainText("PROJECT");

  const viewportFits = await page.evaluate(
    () => document.documentElement.scrollWidth <= window.innerWidth,
  );
  expect(viewportFits).toBeTruthy();
});

test("approves a new hire and provisions a company-managed identity", async ({
  page,
}, testInfo) => {
  const suffix = uniqueSuffix(testInfo.project.name).toLowerCase();
  employeeSuffixes.set(testInfo.project.name, suffix);
  await page.getByRole("link", { name: "Employees" }).click();
  await expect(page.getByRole("heading", { name: "Employee onboarding" })).toBeVisible();

  await page.getByLabel("Employee number").fill(`E-${suffix}`);
  await page.getByLabel("First name").fill("Jordan");
  await page.getByLabel("Last name").fill("Builder");
  await page.getByLabel("Personal email").fill(`${suffix}@example.com`);
  await page.getByLabel("Company username").fill(`jordan.${suffix.slice(-12)}`);
  await page.getByRole("button", { name: "Create employee draft" }).click();

  const employee = page
    .getByText(`E-${suffix}`, { exact: false })
    .locator("xpath=ancestor::li");
  await expect(employee).toContainText("DRAFT");
  await employee.getByRole("button", { name: "Approve" }).click();
  await expect(page.getByText("Status:").locator("..")).toContainText("CREATED", {
    timeout: 20_000,
  });
  await expect(page.getByText(/^Directory user ID: [a-f0-9-]{36}$/)).toBeVisible();
  const activationPanel = page.getByRole("region", { name: "Activation handoff" });
  await expect(activationPanel.locator(".status-badge")).toHaveText("Invitation sent", {
    timeout: 20_000,
  });
  await activationPanel.getByRole("button", { name: "Open local email preview" }).click();
  const activation = page.getByRole("link", { name: "Open employee activation" });
  await expect(activation).toBeVisible();
  const activationUrl = await activation.getAttribute("href");
  if (!activationUrl) throw new Error("Mock activation URL was not available");
  await page.goto(activationUrl);
  await expect(page.getByRole("heading", { name: "Set your ERP password" })).toBeVisible({
    timeout: 20_000,
  });
  await page.getByLabel("Create password").fill(employeePassword);
  await page.getByLabel("Confirm password").fill(employeePassword);
  await page.getByRole("button", { name: "Activate account" }).click();
  await expect(page.getByRole("heading", { name: "You’re all set" })).toBeVisible();
});

test("dispatches an employee to project work and shows the assignment", async ({
  page,
}, testInfo) => {
  const projectSuffix = projectSuffixes.get(testInfo.project.name);
  const employeeSuffix = employeeSuffixes.get(testInfo.project.name);
  if (!projectSuffix || !employeeSuffix) {
    throw new Error("Scheduling prerequisites were not created by this browser project");
  }
  await page.getByRole("link", { name: "Schedule" }).click();
  await expect(page.getByRole("heading", { name: "Dispatch schedule" })).toBeVisible();
  await page.getByRole("combobox", { name: "Project", exact: true }).selectOption({
    label: `E2E-P-${projectSuffix} · E2E Addition ${projectSuffix}`,
  });
  await page.getByLabel("Employee").selectOption({
    label: `E-${employeeSuffix} · Jordan Builder`,
  });
  await page.getByLabel("Work activity").fill(`Site mobilization ${projectSuffix}`);
  await page.getByLabel("Site or location").fill("Verified E2E project site");
  await page.getByLabel("Assignment role").fill("Lead Carpenter");
  await page.getByLabel("Required tools").fill("PPE and layout tools");
  await page.getByRole("button", { name: "Assign to schedule" }).click();

  const entry = page.getByText(`Site mobilization ${projectSuffix}`).locator("..");
  await expect(entry).toContainText(`E2E Addition ${projectSuffix}`);
  await expect(entry).toContainText("Jordan Builder");
  await expect(entry).toContainText("Verified E2E project site");
});

test("queues daily time offline and synchronizes it without duplication", async ({
  page,
  context,
}, testInfo) => {
  const projectSuffix = projectSuffixes.get(testInfo.project.name);
  const employeeSuffix = employeeSuffixes.get(testInfo.project.name);
  if (!projectSuffix || !employeeSuffix) {
    throw new Error("Timekeeping prerequisites were not created by this browser project");
  }
  await page.getByRole("link", { name: "Time" }).click();
  await expect(page.getByRole("heading", { name: "Daily time" })).toBeVisible();
  await page.getByLabel("Employee").selectOption({
    label: `E-${employeeSuffix} · Jordan Builder`,
  });
  await page.getByRole("combobox", { name: "Project", exact: true }).selectOption({
    label: `E2E-P-${projectSuffix} · E2E Addition ${projectSuffix}`,
  });
  const yesterday = new Date(Date.now() - 24 * 60 * 60 * 1000)
    .toISOString()
    .slice(0, 10);
  await page.getByLabel("Work date").fill(yesterday);
  await page.getByLabel("Work performed").fill(`Offline field work ${projectSuffix}`);
  await page.getByLabel("Cost code").fill("01-100");
  await page.getByLabel("Labor category").fill("CARPENTER");

  await context.setOffline(true);
  await expect(page.getByText("Offline", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Queue daily time" }).click();
  await expect(page.getByText("1 operation waiting to sync")).toBeVisible();

  await context.setOffline(false);
  await expect(page.getByText("0 operations waiting to sync")).toBeVisible({
    timeout: 20_000,
  });
  await expect(page.getByText(`Offline field work ${projectSuffix}`)).toBeVisible();
});

async function fillWorkflow(page: Page, suffix: string) {
  await page.getByLabel("Customer name").fill(`E2E Customer ${suffix}`);
  await page.getByLabel("Email", { exact: true }).fill(`e2e-${suffix}@example.com`);
  await page.getByLabel("Project request").fill("Build a verified residential addition");
  await page.getByLabel("Street address").fill(`${suffix.slice(-4)} Test Site Road`);
  await page.getByLabel("ZIP code").fill("97720");
  await page.getByLabel("Scope description").fill("Mobilization and site protection");
  await page.getByLabel("Unit cost").fill("1000");
  await page.getByLabel("Project name").fill(`E2E Addition ${suffix}`);
  await page.getByLabel("Project number").fill(`E2E-P-${suffix}`);
  await page.getByLabel("Contract number").fill(`E2E-C-${suffix}`);
}

async function advance(page: Page, action: string, nextAction: string) {
  await page.getByRole("button", { name: action }).click();
  await expect(page.getByRole("button", { name: nextAction })).toBeVisible();
}

function uniqueSuffix(projectName: string) {
  const random = Math.random().toString(36).slice(2, 8);
  return `${projectName.replaceAll(/[^a-z0-9]/gi, "-")}-${Date.now()}-${random}`;
}
