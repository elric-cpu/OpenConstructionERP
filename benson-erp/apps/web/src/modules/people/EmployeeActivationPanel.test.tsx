import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";

import type { Employee } from "./types";
import { EmployeeActivationPanel } from "./EmployeeActivationPanel";

const employee: Employee = {
  id: "employee-1",
  employee_number: "E-104",
  first_name: "Taylor",
  last_name: "Reed",
  preferred_name: null,
  personal_email: "taylor@example.com",
  company_username: "taylor.reed",
  company_email: "taylor@benson.example",
  hire_date: "2026-07-26",
  status: "IDENTITY_CREATED",
  activation_sent_at: "2026-07-26T16:00:00Z",
  erp_access_confirmed_at: null,
  version: 4,
};

function renderPanel(value = employee) {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <EmployeeActivationPanel employee={value} />
    </QueryClientProvider>,
  );
}

test("shows activation status and opens the local mock delivery", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({
      activation_url: "http://benson-ai/activate#token=one-time-token",
      expires_at: "2026-07-27T16:00:00Z",
    }),
  });
  vi.stubGlobal("fetch", fetchMock);
  renderPanel();

  expect(screen.getAllByText("Invitation sent")).toHaveLength(2);
  fireEvent.click(screen.getByRole("button", { name: "Open local email preview" }));

  const link = await screen.findByRole("link", { name: "Open employee activation" });
  expect(link).toHaveAttribute("href", "http://benson-ai/activate#token=one-time-token");
  expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/employees/employee-1/activation-preview",
    expect.objectContaining({ credentials: "include" }),
  );
});

test("requires a reason and queues a version-checked replacement invitation", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    status: 200,
    json: async () => ({ id: "activation-2", employee_id: employee.id }),
  });
  vi.stubGlobal("fetch", fetchMock);
  renderPanel();

  fireEvent.change(screen.getByLabelText("Resend reason"), { target: { value: "short" } });
  expect(screen.getByRole("button", { name: "Send new activation link" })).toBeDisabled();
  fireEvent.change(screen.getByLabelText("Resend reason"), {
    target: { value: "Employee did not receive the original invitation." },
  });
  fireEvent.click(screen.getByRole("button", { name: "Send new activation link" }));

  expect(await screen.findByRole("status")).toHaveTextContent("queued for delivery");
  await waitFor(() => expect(fetchMock).toHaveBeenCalledWith(
    "/api/v1/employees/employee-1/activation/reissue",
    expect.objectContaining({
      body: JSON.stringify({ reason: "Employee did not receive the original invitation." }),
      headers: expect.any(Headers),
    }),
  ));
  const headers = fetchMock.mock.calls[0][1].headers as Headers;
  expect(headers.get("If-Match")).toBe("4");
});

test("shows confirmed access without resend controls", () => {
  renderPanel({ ...employee, status: "ACTIVE", erp_access_confirmed_at: "2026-07-26T18:00:00Z" });
  expect(screen.getByText("Access confirmed")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Send new activation link" })).not.toBeInTheDocument();
});
