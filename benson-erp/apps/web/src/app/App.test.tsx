import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";

import { App } from "./App";
import { AuthProvider } from "./AuthContext";

const testAccessToken = `e30.${btoa(
  JSON.stringify({
    sub: "11111111-1111-4111-8111-111111111111",
    tenant: "22222222-2222-4222-8222-222222222222",
  }),
)}.signature`;

function renderApp() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/login"]}>
        <AuthProvider>
          <App />
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

test("signs in and opens the real lead workflow", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: testAccessToken,
        token_type: "bearer",
        expires_in: 900,
        csrf_token: "csrf-token-with-at-least-thirty-two-characters",
      }),
    }),
  );
  renderApp();
  expect(await screen.findByRole("heading", { name: "Sign in to the ERP" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Work email"), {
    target: { value: "admin@bensonhomesolutions.com" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "correct-password-value" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await waitFor(() => {
    expect(screen.getByRole("heading", { name: "Lead to project" })).toBeInTheDocument();
  });
  expect(screen.getByRole("button", { name: "Create lead" })).toBeEnabled();
});

test("completes an MFA challenge before opening the ERP", async () => {
  const fetchMock = vi
    .fn()
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: null,
        csrf_token: null,
        expires_in: 0,
        mfa_required: true,
        mfa_challenge_token: "signed-mfa-challenge-token-with-enough-length",
      }),
    })
    .mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => ({
        access_token: testAccessToken,
        csrf_token: "csrf-token-with-at-least-thirty-two-characters",
        expires_in: 900,
        mfa_required: false,
        mfa_challenge_token: null,
      }),
    });
  vi.stubGlobal("fetch", fetchMock);
  renderApp();
  await screen.findByRole("heading", { name: "Sign in to the ERP" });
  fireEvent.change(screen.getByLabelText("Work email"), {
    target: { value: "admin@bensonhomesolutions.com" },
  });
  fireEvent.change(screen.getByLabelText("Password"), {
    target: { value: "correct-password-value" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  const code = await screen.findByLabelText("Authentication or recovery code");
  fireEvent.change(code, { target: { value: "123456" } });
  fireEvent.click(screen.getByRole("button", { name: "Verify code" }));
  expect(await screen.findByRole("heading", { name: "Lead to project" })).toBeInTheDocument();
  expect(fetchMock).toHaveBeenCalledTimes(2);
});

test("drives the visible workflow from lead intake through project creation", async () => {
  const responses = [
    { access_token: testAccessToken, token_type: "bearer", expires_in: 900, csrf_token: "csrf-token-with-at-least-thirty-two-characters" },
    { id: "lead-1", version: 1, status: "NEW" },
    { id: "lead-1", version: 2, status: "QUALIFIED" },
    { customer_id: "customer-1", property_id: "property-1" },
    { id: "estimate-1", version: 1, total: "0.00", status: "DRAFT" },
    { id: "estimate-1", version: 2, total: "1200.00", status: "DRAFT" },
    { id: "estimate-1", version: 3, total: "1200.00", status: "APPROVED" },
    { id: "proposal-1", version: 1, status: "SENT", document_checksum: "a".repeat(64), price_snapshot: { total: "1200.00" } },
    { id: "proposal-1", version: 2, status: "ACCEPTED", document_checksum: "a".repeat(64), price_snapshot: { total: "1200.00" } },
    { project: { id: "project-1", project_number: "PRJ-001", name: "Smith Addition" }, contract_value: "1200.00", budget_line_count: 1 },
  ];
  vi.stubGlobal(
    "fetch",
    vi.fn().mockImplementation(async () => {
      const body = responses.shift();
      return { ok: true, status: 200, json: async () => body };
    }),
  );
  renderApp();
  await screen.findByRole("heading", { name: "Sign in to the ERP" });
  fireEvent.change(screen.getByLabelText("Work email"), { target: { value: "admin@bensonhomesolutions.com" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct-password-value" } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
  await screen.findByRole("heading", { name: "Lead to project" });

  const values: Array<[string, string]> = [
    ["Customer name", "Sam Smith"],
    ["Email", "sam@customer.com"],
    ["Project request", "Build a residential addition"],
    ["Street address", "100 Main Street"],
    ["ZIP code", "97720"],
    ["Scope description", "Mobilization"],
    ["Unit cost", "1000"],
    ["Project name", "Smith Addition"],
    ["Project number", "PRJ-001"],
    ["Contract number", "CON-001"],
  ];
  values.forEach(([label, value]) => {
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  });
  for (const action of [
    "Create lead",
    "Qualify lead",
    "Create customer and property",
    "Start estimate",
    "Add estimate line",
    "Approve estimate",
    "Issue proposal",
  ]) {
    fireEvent.click(await screen.findByRole("button", { name: action }));
  }
  fireEvent.click(await screen.findByLabelText(/I reviewed and accept the proposal/));
  fireEvent.click(screen.getByRole("button", { name: "Record acceptance" }));
  fireEvent.click(await screen.findByRole("button", { name: "Create contract and project" }));
  expect(await screen.findByRole("heading", { name: "Smith Addition" })).toBeInTheDocument();
  expect(screen.getByText("$1200.00")).toBeInTheDocument();
  expect(responses).toHaveLength(0);
});
